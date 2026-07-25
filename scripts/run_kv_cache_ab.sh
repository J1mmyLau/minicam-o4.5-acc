#!/bin/bash
# P6 KV Cache Reuse Formal A/B — Persistent Background Runner
# 8 passes × 9 cases = 72 executions (36A + 36B)
# Pass order: A, B, B, A, B, A, A, B  (ABBA+BAAB)
#
# Launch: nohup bash scripts/run_kv_cache_ab.sh > logs/kv_cache_ab.log 2>&1 &
# Resume: re-run same command; completed cases are skipped via progress file.

set -o pipefail

BINARY="/workspace/llama.cpp-omni-ngl8-e2e/build-cann91/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TEST_PREFIX="/workspace/llama.cpp-omni-ngl8-e2e/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p6-ab"
LOGDIR="${OUTDIR}/logs"
CSV="${OUTDIR}/kv_cache_ab_raw.csv"
INVALID_CSV="${OUTDIR}/invalid_samples.csv"
PROGRESS="${OUTDIR}/.progress"
PIDFILE="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/logs/kv_cache_ab.pid"
EXITCODE_FILE="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/logs/kv_cache_ab.exit_code"
DONE_FILE="/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/logs/kv_cache_ab.done"
CASES=9
PER_CASE_TIMEOUT=150

mkdir -p "$OUTDIR" "$LOGDIR" "$(dirname "$PIDFILE")"

# Write PID
echo $$ > "$PIDFILE"
echo "PID: $$  → $PIDFILE"

# ─── Cleanup trap ───────────────────────────────
cleanup() {
    echo "[$(date -Iseconds)] CLEANUP: runner exiting (signal received)"
    # Kill child processes in our process group
    jobs -p 2>/dev/null | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ─── Helpers ────────────────────────────────────

is_completed() {
    local pass_id=$1 arm=$2 case_id=$3
    grep -q "^${pass_id},${arm},${case_id}$" "${PROGRESS}" 2>/dev/null
}

mark_completed() {
    local pass_id=$1 arm=$2 case_id=$3
    echo "${pass_id},${arm},${case_id}" >> "${PROGRESS}"
}

log_ts() {
    echo "[$(date -Iseconds)] $*"
}

# ─── Run a single case ──────────────────────────

run_case() {
    local pass_id=$1 arm=$2 case_id=$3
    local cache_enabled=0
    [ "$arm" = "B" ] && cache_enabled=1

    local label="P${pass_id}_${arm}_c${case_id}"
    local stdout_log="${LOGDIR}/${label}_stdout.log"
    local stderr_log="${LOGDIR}/${label}_stderr.log"

    local kv_env=""
    [ "$cache_enabled" = "1" ] && kv_env="OMNI_KV_CACHE_REUSE=1"

    log_ts "START ${label} arm=${arm} cache=${cache_enabled}"

    # ── Execute ──
    local rc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 $kv_env \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start "$case_id" \
        > "$stdout_log" 2> "$stderr_log" || rc=$?

    local timestamp=$(date -Iseconds)

    # ── Extract metrics from stderr ──

    # First Audio — check stdout first (where 首响时间 is printed), then stderr as fallback
    local fa=$(grep -oP '首响时间.*?:\s*\K\d+' "$stdout_log" | head -1)
    [ -z "$fa" ] && fa=$(grep -oP '首响时间.*?:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$fa" ] && fa=""

    # Prefill time — in stdout (but also check stderr as fallback)
    local prefill_s=$(grep -oP 'prefill \d+ \(audio\+vision\) : \K[0-9.]+' "$stdout_log" | head -1)
    [ -z "$prefill_s" ] && prefill_s=$(grep -oP 'prefill \d+ \(audio\+vision\) : \K[0-9.]+' "$stderr_log" | head -1)
    local prefill_ms=""
    if [ -n "$prefill_s" ]; then
        prefill_ms=$(awk "BEGIN {printf \"%.1f\", ${prefill_s} * 1000}")
    fi

    # KV cache stats
    local cache_hit=$(grep -oP 'cache_hits:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$cache_hit" ] && cache_hit="0"
    local cache_miss=$(grep -oP 'cache_misses:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$cache_miss" ] && cache_miss="0"
    local reused_tokens=$(grep -oP 'tokens_reused:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$reused_tokens" ] && reused_tokens="0"

    # WAV count — T2W wav lines are in stdout (T2W线程: wav_X.wav)
    local wav_count=$(grep -c 'T2W.*wav_.*\.wav' "$stdout_log" 2>/dev/null)
    [ -z "$wav_count" ] && wav_count=$(grep -c 'wav_.*\.wav' "$stderr_log" 2>/dev/null)
    [ -z "$wav_count" ] && wav_count="0"

    # Output tokens — total_generated_tokens is in stdout
    local output_tokens=$(grep -oP 'total_generated_tokens=\K\d+' "$stdout_log" | tail -1)
    [ -z "$output_tokens" ] && output_tokens=$(grep -oP 'total_generated_tokens=\K\d+' "$stderr_log" | tail -1)
    [ -z "$output_tokens" ] && output_tokens=""

    # Degeneration / retry
    local degen=$(grep -oP 'degeneration_detected:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$degen" ] && degen="0"
    local retry=$(grep -oP 'retry_attempted:\s*\K\d+' "$stderr_log" | head -1)
    [ -z "$retry" ] && retry="0"

    # CANN error detection
    local cann_error="0"
    grep -qEi 'CANN.*error|aclrt.*error|aclError|ASCEND.*error|npu.*error|npu.*fail' "$stderr_log" && cann_error="1"

    # E2E time from log timestamps (wall clock)
    local e2e_ms=""
    local first_ts=$(grep -oP '^\d{2}:\d{2}:\d{2}\.\d{3}' "$stderr_log" | head -1)
    local last_ts=$(grep -oP '^\d{2}:\d{2}:\d{2}\.\d{3}' "$stderr_log" | tail -1)
    if [ -n "$first_ts" ] && [ -n "$last_ts" ]; then
        local t1=$(echo "$first_ts" | awk -F'[:.]' '{print ($1*3600 + $2*60 + $3)*1000 + $4}')
        local t2=$(echo "$last_ts" | awk -F'[:.]' '{print ($1*3600 + $2*60 + $3)*1000 + $4}')
        e2e_ms=$((t2 - t1))
    fi

    # ── Validity gates ──
    local valid="1"
    local invalid_reason=""

    if [ "$rc" = "124" ]; then
        valid="0"; invalid_reason="timeout_124"
    elif [ "$rc" != "0" ] && [ "$rc" != "143" ]; then
        # rc=143 is SIGTERM from timeout, also invalid
        valid="0"; invalid_reason="nonzero_rc_${rc}"
    elif [ -z "$fa" ]; then
        valid="0"; invalid_reason="no_first_audio"
    elif [ "$arm" = "B" ] && [ "$cache_hit" = "0" ] && [ "$cache_miss" = "0" ]; then
        valid="0"; invalid_reason="candidate_no_cache_activity"
    elif [ "$cann_error" = "1" ]; then
        valid="0"; invalid_reason="cann_error_detected"
    elif [ "$wav_count" = "0" ]; then
        valid="0"; invalid_reason="no_wav_output"
    fi

    # rc=143 is SIGTERM from timeout → mark as timeout too
    if [ "$rc" = "143" ]; then
        valid="0"; invalid_reason="timeout_143"
    fi

    # Sequence position (0-based case order within pass)
    local seq_pos=""
    case "${pass_id}:${direction_map[$pass_id]}" in
        1:fwd)  seq_pos=$case_id ;;
        2:fwd)  seq_pos=$case_id ;;
        3:rev)  seq_pos=$((CASES - 1 - case_id)) ;;
        4:rev)  seq_pos=$((CASES - 1 - case_id)) ;;
        5:fwd)  seq_pos=$case_id ;;
        6:fwd)  seq_pos=$case_id ;;
        7:rev)  seq_pos=$((CASES - 1 - case_id)) ;;
        8:rev)  seq_pos=$((CASES - 1 - case_id)) ;;
    esac

    # ── Write CSV row (immediate append) ──
    local csv_line="${timestamp},${pass_id},${seq_pos},${arm},${case_id},${cache_enabled},${cache_hit},${cache_miss},${reused_tokens},${fa},${prefill_ms},${e2e_ms},${wav_count},${output_tokens},${degen},${retry},${cann_error},${rc},${valid},${invalid_reason}"
    echo "$csv_line" >> "$CSV"

    if [ "$valid" = "0" ]; then
        echo "$csv_line" >> "$INVALID_CSV"
        log_ts "INVALID ${label}: reason=${invalid_reason} rc=${rc} fa=${fa} wavs=${wav_count}"
    else
        log_ts "OK     ${label}: FA=${fa}ms prefill=${prefill_ms}ms wavs=${wav_count} tokens=${output_tokens} cache_hit=${cache_hit} cache_miss=${cache_miss} reused=${reused_tokens}"
    fi
}

# ─── Main ───────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  P6 KV Cache Reuse Formal A/B Runner    ║"
echo "║  8 passes × 9 cases = 72 executions     ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Started: $(date -Iseconds)"
echo "PID: $$"
echo "Binary: $BINARY"
echo "CSV:    $CSV"
echo ""

# Write CSV header (only if new file)
if [ ! -f "$CSV" ]; then
    echo "timestamp,pass_id,seq_pos,arm,case_id,cache_enabled,cache_hit,cache_miss,reused_tokens,first_audio_ms,prefill_ms,e2e_ms,wav_count,output_tokens,degeneration_detected,retry_count,cann_error,return_code,valid,invalid_reason" > "$CSV"
    log_ts "CSV header written"
fi

# ─── Prime Step: Ensure fresh KV cache ─────────

echo ""
echo "───── PRIME: Fresh KV cache population ─────"

PRIME_KEY="PRIME"
if grep -q "^${PRIME_KEY}$" "${PROGRESS}" 2>/dev/null; then
    log_ts "PRIME already done, skipping"
else
    # Clear any stale cache
    rm -f /tmp/omni_kvcache_*.bin
    log_ts "Cleared old KV cache files"

    # Run B arm on case 0 to prime the cache (not counted in CSV)
    prime_stdout="${LOGDIR}/PRIME_stdout.log"
    prime_stderr="${LOGDIR}/PRIME_stderr.log"

    log_ts "PRIME: Running B/case0 to populate KV cache..."
    prc=0
    env OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_KV_CACHE_REUSE=1 \
        timeout $PER_CASE_TIMEOUT "$BINARY" \
        -m "$MODEL" -ngl 0 --omni \
        --test "$TEST_PREFIX" 1 --test-start 0 \
        > "$prime_stdout" 2> "$prime_stderr" || prc=$?

    pcache_hit=$(grep -oP 'cache_hits:\s*\K\d+' "$prime_stderr" | head -1)
    pcache_miss=$(grep -oP 'cache_misses:\s*\K\d+' "$prime_stderr" | head -1)
    preused=$(grep -oP 'tokens_reused:\s*\K\d+' "$prime_stderr" | head -1)
    [ -z "$pcache_hit" ] && pcache_hit="0"
    [ -z "$pcache_miss" ] && pcache_miss="0"
    [ -z "$preused" ] && preused="0"

    log_ts "PRIME done: rc=${prc} cache_hit=${pcache_hit} cache_miss=${pcache_miss} reused_tokens=${preused}"

    # Gate: if prime didn't save cache, abort
    if [ ! -f /tmp/omni_kvcache_*.bin ]; then
        log_ts "FATAL: PRIME failed — no cache file created. Aborting."
        echo "1" > "$EXITCODE_FILE"
        exit 1
    fi

    echo "${PRIME_KEY}" >> "${PROGRESS}"
    log_ts "Cache file created: $(ls -la /tmp/omni_kvcache_*.bin 2>/dev/null)"
fi

# ─── Define passes (ordered) ───────────────────
# pass_id,arm,direction
# Direction: fwd=cases 0→8, rev=cases 8→0
declare -a PASS_SPECS=(
    "1,A,fwd"
    "2,B,fwd"
    "3,B,rev"
    "4,A,rev"
    "5,B,fwd"
    "6,A,fwd"
    "7,A,rev"
    "8,B,rev"
)

# Build direction lookup map for seq_pos computation
declare -A direction_map
for spec in "${PASS_SPECS[@]}"; do
    IFS=',' read -r pid parm pdir <<< "$spec"
    direction_map[$pid]="$pdir"
done

# ─── Execute all passes ────────────────────────

total_ran=0
total_skipped=0
total_invalid=0

for spec in "${PASS_SPECS[@]}"; do
    IFS=',' read -r pass_id arm direction <<< "$spec"

    echo ""
    echo "───── Pass ${pass_id}: Arm=${arm} Direction=${direction} ─────"

    # Build case iteration order
    if [ "$direction" = "fwd" ]; then
        case_list=$(seq 0 $((CASES - 1)))
    else
        case_list=$(seq $((CASES - 1)) -1 0)
    fi

    for case_id in $case_list; do
        if is_completed "$pass_id" "$arm" "$case_id"; then
            log_ts "SKIP  P${pass_id}_${arm}_c${case_id} (already completed)"
            total_skipped=$((total_skipped + 1))
            continue
        fi

        run_case "$pass_id" "$arm" "$case_id"
        total_ran=$((total_ran + 1))

        # Mark as completed regardless of validity
        mark_completed "$pass_id" "$arm" "$case_id"

        # Count invalids from last CSV line
        last_valid=$(tail -1 "$CSV" | awk -F, '{print $19}')
        if [ "$last_valid" = "0" ]; then
            total_invalid=$((total_invalid + 1))
        fi

        # Brief NPU cooldown between cases
        sleep 2
    done
done

# ─── Done ──────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  P6 A/B Runner Complete                 ║"
echo "╚══════════════════════════════════════════╝"
echo "Finished: $(date -Iseconds)"
echo "Total ran:      $total_ran"
echo "Total skipped:  $total_skipped"
echo "Total invalid:  $total_invalid"
echo "CSV:            $CSV"
echo "Logs:           $LOGDIR"

# Completion markers
echo "0" > "$EXITCODE_FILE"
echo "$(date -Iseconds)" > "$DONE_FILE"
log_ts "Done marker written to $DONE_FILE"

# Quick summary
if [ -f "$CSV" ]; then
    valid_count=$(tail -n +2 "$CSV" 2>/dev/null | awk -F, '$19==1' | wc -l)
    invalid_count=$(tail -n +2 "$CSV" 2>/dev/null | awk -F, '$19==0' | wc -l)
    a_valid=$(tail -n +2 "$CSV" 2>/dev/null | awk -F, '$4=="A" && $19==1' | wc -l)
    b_valid=$(tail -n +2 "$CSV" 2>/dev/null | awk -F, '$4=="B" && $19==1' | wc -l)
    echo "Valid samples:   $valid_count (A=$a_valid, B=$b_valid)"
    echo "Invalid samples: $invalid_count"
fi

exit 0
