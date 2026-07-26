#!/bin/bash
# P5: Supplemental KV Cache Reuse A/B — with fixed T2W drain
# ≥30 matched pairs. Gate: rc0_without_audio=0, valid_rate > P6 rate
#
# Launch: nohup bash scripts/run_kv_cache_ab_p5.sh > /workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p5-ab/runner.log 2>&1 &
set -Eeuo pipefail

BINARY="/workspace/llama.cpp-omni-ngl8-e2e/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-ngl8-e2e/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p5-ab"
LOGDIR="${OUTDIR}/logs"
CSV="${OUTDIR}/kv_cache_ab_p5.csv"
PROGRESS="${OUTDIR}/.progress"
PIDFILE="${OUTDIR}/.pid"
DONE_FILE="${OUTDIR}/.done"
EXITCODE_FILE="${OUTDIR}/.exit_code"

CASES="0 1 3 5"  # 4 fast cases (skip case 2 which has long responses)
NCASES=4
PASSES=16  # 8 AB pairs × 4 cases = 32 matched pairs
PER_CASE_TIMEOUT=120
MAX_PARALLEL=3

mkdir -p "$OUTDIR" "$LOGDIR"

# ─── PID + cleanup ───
echo $$ > "$PIDFILE"

cleanup() {
    local exit_code=$?
    echo "[$(date -Iseconds)] CLEANUP: runner exiting (code=$exit_code)"
    # Kill running child processes
    jobs -p 2>/dev/null | xargs -r kill 2>/dev/null || true
    echo "$exit_code" > "$EXITCODE_FILE"
    echo "$(date -Iseconds)" > "$DONE_FILE"
}
trap cleanup EXIT INT TERM

echo "PID: $$"
echo "Started: $(date -Iseconds)"
echo "Passes: $PASSES (ABAB... = 8 pairs × 4 cases = 32 matched pairs)"
echo "Total executions: $((PASSES * NCASES)) ($((PASSES * NCASES / 2)) A + $((PASSES * NCASES / 2)) B)"
echo "Max parallel: $MAX_PARALLEL"
echo "CSV: $CSV"

# ─── Helpers ───

is_completed() { grep -q "^${1},${2},${3}$" "${PROGRESS}" 2>/dev/null; }
mark_completed() { echo "${1},${2},${3}" >> "${PROGRESS}"; }

# ─── Run a single case ───

run_case() {
    local pass_id=$1 arm=$2 case_id=$3
    local cache_enabled=0
    [ "$arm" = "B" ] && cache_enabled=1

    local label="P${pass_id}_${arm}_c${case_id}"
    local stdout_log="${LOGDIR}/${label}_stdout.log"
    local stderr_log="${LOGDIR}/${label}_stderr.log"

    local kv_env=""
    [ "$cache_enabled" = "1" ] && kv_env="OMNI_KV_CACHE_REUSE=1"

    local rc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 $kv_env \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start "$case_id" \
        > "$stdout_log" 2> "$stderr_log" || rc=$?

    local timestamp=$(date -Iseconds)

    # decode_to_first_audio (first number after 首响时间)
    local dfa=$(grep -oP '首响时间.*?:\s*\K\d+' "$stdout_log" | head -1)
    [ -z "$dfa" ] && dfa=""

    # request_to_first_audio (second number, after |)
    local rfa=$(grep -oP '\|\s*\K\d+(?=ms \(request_to_first_audio\))' "$stdout_log" | head -1)
    [ -z "$rfa" ] && rfa=""

    # Prefill time
    local prefill_s=$(grep -oP 'prefill \d+ \(audio\+vision\) : \K[0-9.]+' "$stdout_log" | head -1)
    local prefill_ms=""
    if [ -n "$prefill_s" ]; then
        prefill_ms=$(awk "BEGIN {printf \"%.1f\", ${prefill_s} * 1000}")
    fi

    # KV cache stats (stderr)
    local cache_hit=$(grep -oP 'cache_hits:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$cache_hit" ] && cache_hit="0"
    local cache_miss=$(grep -oP 'cache_misses:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$cache_miss" ] && cache_miss="0"
    local reused_tokens=$(grep -oP 'tokens_reused:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$reused_tokens" ] && reused_tokens="0"

    # WAV count — use head -1 to avoid "0\n0" when grep -c prints 0 AND exits 1
    local wav_count=$(grep -c 'T2W.*wav_.*\.wav' "$stdout_log" 2>/dev/null | head -1)
    [ -z "$wav_count" ] && wav_count="0"

    # Output tokens
    local output_tokens=$(grep -oP 'total_generated_tokens=\K\d+' "$stdout_log" | tail -1)
    [ -z "$output_tokens" ] && output_tokens=""

    # T2W terminal classification (stdout, tail -1 for final determination)
    local terminal=$(grep -oP 'T2W terminal:\s*\K\w+' "$stdout_log" | tail -1)
    [ -z "$terminal" ] && terminal="UNKNOWN"

    # Validity gates
    local valid="1"
    local invalid_reason=""

    if [ "$rc" = "124" ] || [ "$rc" = "143" ]; then
        valid="0"; invalid_reason="timeout_${rc}"
    elif [ "$rc" != "0" ]; then
        valid="0"; invalid_reason="nonzero_rc_${rc}"
    elif [ "$rc" = "0" ] && [ "$wav_count" = "0" ]; then
        valid="0"; invalid_reason="rc0_without_audio"
    elif [ "$terminal" = "DRAIN_TIMEOUT" ]; then
        valid="0"; invalid_reason="drain_timeout"
    elif [ "$terminal" = "PIPELINE_FAILURE" ]; then
        valid="0"; invalid_reason="pipeline_failure"
    elif [ "$terminal" = "OUTPUT_BLOCKED" ]; then
        valid="0"; invalid_reason="output_blocked"
    fi

    # CSV row: 1=ts 2=pass 3=arm 4=case 5=cache 6=hit 7=miss 8=reused 9=dfa 10=rfa 11=prefill 12=wav 13=tokens 14=term 15=rc 16=valid 17=reason
    echo "${timestamp},${pass_id},${arm},${case_id},${cache_enabled},${cache_hit},${cache_miss},${reused_tokens},${dfa},${rfa},${prefill_ms},${wav_count},${output_tokens},${terminal},${rc},${valid},${invalid_reason}" >> "$CSV"

    if [ "$valid" = "0" ]; then
        echo "[$(date -Iseconds)] INVALID ${label}: ${invalid_reason} rc=${rc} wavs=${wav_count}"
    else
        echo "[$(date -Iseconds)] OK     ${label}: dfa=${dfa}ms rfa=${rfa}ms prefill=${prefill_ms}ms wavs=${wav_count} tokens=${output_tokens} cache_hit=${cache_hit}"
    fi
}

# ─── CSV header ───
if [ ! -f "$CSV" ]; then
    echo "timestamp,pass_id,arm,case_id,cache_enabled,cache_hit,cache_miss,reused_tokens,decode_fa_ms,request_fa_ms,prefill_ms,wav_count,output_tokens,terminal,return_code,valid,invalid_reason" > "$CSV"
fi

# ─── Prime: Populate KV cache ───

PRIME_KEY="PRIME"
if grep -q "^${PRIME_KEY}$" "${PROGRESS}" 2>/dev/null; then
    echo "[$(date -Iseconds)] PRIME already done, skipping"
else
    rm -f /tmp/omni_kvcache_*.bin
    echo "[$(date -Iseconds)] PRIME: Populating KV cache with B/case0..."

    prc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000 OMNI_KV_CACHE_REUSE=1 \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start 0 \
        > "${LOGDIR}/PRIME_stdout.log" 2> "${LOGDIR}/PRIME_stderr.log" || prc=$?

    echo "[$(date -Iseconds)] PRIME done: rc=${prc}"
    if ! ls /tmp/omni_kvcache_*.bin >/dev/null 2>&1; then
        echo "FATAL: PRIME failed — no cache file created"
        exit 1
    fi
    echo "${PRIME_KEY}" >> "${PROGRESS}"
    echo "[$(date -Iseconds)] Cache file: $(ls -la /tmp/omni_kvcache_*.bin 2>/dev/null)"
fi

# ─── Main execution ───

echo ""
echo "═══════════════════════════════════════════"
echo "  P5 KV Cache A/B — 16 passes (ABAB...)"
echo "═══════════════════════════════════════════"
echo ""

running=0
for pass_id in $(seq 1 $PASSES); do
    # Odd passes = A, Even passes = B
    if [ $((pass_id % 2)) -eq 1 ]; then
        arm="A"
    else
        arm="B"
    fi

    for case_id in $CASES; do
        if is_completed "$pass_id" "$arm" "$case_id"; then
            continue
        fi

        while [ $running -ge $MAX_PARALLEL ]; do
            wait -n 2>/dev/null || true
            running=$((running - 1))
        done

        run_case "$pass_id" "$arm" "$case_id" &
        mark_completed "$pass_id" "$arm" "$case_id"
        running=$((running + 1))
        sleep 1
    done
done

# Wait for remaining
echo ""
echo "Waiting for remaining $running jobs..."
wait

# ─── Summary (corrected column indices: $16=valid, $17=reason) ───

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  P5 KV Cache A/B Complete               ║"
echo "╚══════════════════════════════════════════╝"
echo "Finished: $(date -Iseconds)"

if [ -f "$CSV" ]; then
    echo ""
    tail -n +2 "$CSV" | awk -F, '{
        total++; arm=$3; v=$16+0; reason=$17;
        gates[reason]++;
        if(v==1) { valid_count++; arm_valid[arm]++; }
        if(arm=="A") { a_total++; if(v==1) { a_rfa+=$10+0; a_dfa+=$9+0; a_pf+=$11+0; } }
        if(arm=="B") { b_total++; if(v==1) { b_rfa+=$10+0; b_dfa+=$9+0; b_pf+=$11+0; } }
        if($12+0==0 && $16+0==0) rc0z++;
    }
    END {
        printf "Total: %d | Valid: %d | Invalid: %d (%.1f%%)\n", total, valid_count, total-valid_count, (total-valid_count)*100/total;
        printf "Arm A: %d valid / %d total\n", arm_valid["A"]+0, a_total;
        printf "Arm B: %d valid / %d total\n", arm_valid["B"]+0, b_total;
        printf "rc0_without_audio: %d\n", rc0z;
        printf "\n--- Metrics (valid samples only) ---\n";
        if(arm_valid["A"]>0) printf "Arm A: avg decode_fa=%.0fms  request_fa=%.0fms  prefill=%.1fms\n", a_dfa/arm_valid["A"], a_rfa/arm_valid["A"], a_pf/arm_valid["A"];
        if(arm_valid["B"]>0) printf "Arm B: avg decode_fa=%.0fms  request_fa=%.0fms  prefill=%.1fms\n", b_dfa/arm_valid["B"], b_rfa/arm_valid["B"], b_pf/arm_valid["B"];
        if(arm_valid["A"]>0 && arm_valid["B"]>0) {
            rfa_delta = b_rfa/arm_valid["B"] - a_rfa/arm_valid["A"];
            printf "\nrequest_fa delta (B-A): %.0fms\n", rfa_delta;
        }
    }'
    echo ""
    for g in $(tail -n +2 "$CSV" | awk -F, '$16+0==0{print $17}' | sort -u); do
        cnt=$(tail -n +2 "$CSV" | awk -F, -v g="$g" '$16+0==0 && $17==g{print}' | wc -l)
        echo "  $g: $cnt"
    done
fi

echo ""
echo "CSV: $CSV"
echo "PID file: $PIDFILE"
echo "Done file: $DONE_FILE"
exit 0
