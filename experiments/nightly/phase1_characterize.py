#!/usr/bin/env python3
"""
PHASE 1 — Complete n_ubatch / FA shape characterization.
Systematic sweep to build empirical FA shape map.
Proper PID tracking, no broad process killing.
"""
import subprocess, json, os, sys, time, select, re
from collections import defaultdict
from datetime import datetime

CLI_BIN = '/workspace/llama.cpp-omni-bench-huawei/build/bin/llama-omni-eval-daily-cli'
MODEL = '/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf'
LOG_DIR = '/workspace/llama.cpp-omni-bench-huawei/experiments/nightly/phase1_logs'
RESULTS_FILE = '/workspace/llama.cpp-omni-bench-huawei/experiments/nightly/phase1_results.jsonl'

os.makedirs(LOG_DIR, exist_ok=True)

def run_textonly_test(label, n_x_tokens, extra_env=None, timeout=300):
    """Run ONE text-only test with tracked PID. Returns results dict."""
    prompt = ("X " * n_x_tokens + "\n\nSay hello.\n")
    stderr_path = os.path.join(LOG_DIR, f'p1_{label}.stderr')

    cmd = [CLI_BIN, '-m', MODEL, '-c', '40960', '-ngl', '999',
           '--n-predict', '32', '--temp', '0.0', '--top-p', '0.8', '--top-k', '100',
           '--repeat-penalty', '1.02', '--seed', '42']
    env = os.environ.copy()
    env['ASCEND_RT_VISIBLE_DEVICES'] = '0'
    env['OMNI_CANN_FA_SHAPE_DIAG'] = '1'
    env['OMNI_CANN_FA_NAN_CHECK'] = '1'
    if extra_env:
        env.update(extra_env)

    pid = None
    wall_start = time.time()
    result_line = ''
    exit_code = None

    try:
        with open(stderr_path, 'w') as err_fh:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=err_fh, env=env)
            pid = proc.pid
            print(f'  [{label}] PID={pid}, n_x={n_x_tokens}', flush=True)

            # Wait for ready signal (up to 120s)
            ready = False
            start = time.time()
            while time.time() - start < 120:
                if proc.poll() is not None:
                    print(f'  [{label}] Process exited early (rc={proc.returncode})', flush=True)
                    break
                r, _, _ = select.select([proc.stdout], [], [], 2.0)
                if r:
                    line = proc.stdout.readline()
                    if not line: break
                    try:
                        if json.loads(line.decode('utf-8')).get('type') == 'ready':
                            ready = True
                            break
                    except: pass

            if ready:
                req = json.dumps({
                    'type': 'infer', 'id': f'p1_{label}',
                    'frames': [], 'audios': [],
                    'prompt': prompt, 'n_predict': 32
                }, ensure_ascii=False) + '\n'
                proc.stdin.write(req.encode('utf-8'))
                proc.stdin.flush()

                # Wait for response (up to timeout)
                decode_start = time.time()
                while time.time() - start < timeout:
                    if proc.poll() is not None:
                        break
                    r, _, _ = select.select([proc.stdout], [], [], 5.0)
                    if r:
                        line = proc.stdout.readline()
                        if line:
                            result_line = line.decode('utf-8', errors='replace')
                            break
                wall_time = time.time() - wall_start

            try:
                proc.stdin.close()
            except: pass

            try:
                exit_code = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print(f'  [{label}] PID={pid} did not exit, terminating', flush=True)
                proc.terminate()
                try:
                    exit_code = proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    print(f'  [{label}] PID={pid} force kill', flush=True)
                    proc.kill()
                    exit_code = proc.wait(timeout=10)

    except Exception as e:
        print(f'  [{label}] ERROR: {e}', flush=True)
        return {'label': label, 'error': str(e), 'pid': pid}

    wall_time = time.time() - wall_start

    # Parse stderr for shapes and NaN
    shapes = []
    nan_shapes = set()
    first_nan_shape = None
    first_nan_time = None
    all_nan_checks = []

    try:
        with open(stderr_path, 'r') as f:
            for i, line in enumerate(f):
                if 'cann_fa_shape' in line and 'Q=' in line:
                    m = re.search(r'q_seq=(\d+)\s+kv_seq=(\d+)', line)
                    if m:
                        shapes.append((int(m.group(1)), int(m.group(2))))
                if 'cann_fa_output' in line:
                    m_q = re.search(r'q_seq=(\d+)\s+kv_seq=(\d+)', line)
                    m_n = re.search(r'nan=(\d+)', line)
                    if m_q and m_n:
                        q, kv = int(m_q.group(1)), int(m_q.group(2))
                        n = int(m_n.group(1))
                        all_nan_checks.append({'q': q, 'kv': kv, 'nan': n})
                        if n > 0:
                            nan_shapes.add((q, kv))
                            if first_nan_shape is None:
                                first_nan_shape = (q, kv)
                                first_nan_time = i  # approximate temporal order
    except Exception as e:
        print(f'  [{label}] Error reading stderr: {e}', flush=True)

    has_nan = len(nan_shapes) > 0

    # Parse result line
    response_text = ''
    if result_line:
        try:
            response_text = json.loads(result_line).get('response', '')
        except: pass

    all_underscores = all(c == '_' for c in response_text) if response_text else False

    # Get unique shapes maintaining temporal order
    seen = set()
    unique_shapes_ordered = []
    for q, kv in shapes:
        if (q, kv) not in seen:
            seen.add((q, kv))
            unique_shapes_ordered.append((q, kv))

    result = {
        'label': label,
        'n_x': n_x_tokens,
        'extra_env': {k: v for k, v in (extra_env or {}).items() if 'OMNI' in k},
        'pid': pid,
        'exit_code': exit_code,
        'wall_time_s': round(wall_time, 1),
        'total_fa_calls': len(shapes),
        'total_nan_calls': sum(1 for c in all_nan_checks if c['nan'] > 0),
        'has_nan': has_nan,
        'all_underscores': all_underscores,
        'first_nan_shape': list(first_nan_shape) if first_nan_shape else None,
        'unique_shapes_ordered': unique_shapes_ordered,
        'nan_shapes': sorted(list(nan_shapes)),
        'response_preview': response_text[:120],
        'response_text': response_text,
    }

    # Write to results file
    with open(RESULTS_FILE, 'a') as f:
        f.write(json.dumps(result) + '\n')

    return result


def verify_threshold():
    """Step 1A: Re-verify Q threshold with current binary."""
    print("\n" + "="*70)
    print("STEP 1A: Verify Q threshold at KV=768 (no n_ubatch override)")
    print("="*70)

    results = {}
    for n_x in [350, 375, 400, 425, 430, 435, 440, 450]:
        label = f'verify_nx{n_x}'
        r = run_textonly_test(label, n_x)
        results[n_x] = r
        kv768_qs = [q for q, kv in r.get('unique_shapes_ordered', []) if kv == 768 and q > 1]
        print(f'  n_x={n_x:4d}: KV768_Qs={kv768_qs}, NaN={r["has_nan"]}, '
              f'first_nan={r["first_nan_shape"]}, resp={r["response_preview"][:60]!r}')

    return results


def n_ubatch_sweep():
    """Step 1B: Sweep n_ubatch with fixed n_x=450 text-only prompt."""
    print("\n" + "="*70)
    print("STEP 1B: n_ubatch sweep (n_x=450, text-only)")
    print("="*70)

    results = {}
    for ubatch in [512, 480, 448, 432, 416, 400, 384, 352, 320, 288, 256]:
        label = f'sweep_ub{ubatch}'
        extra = {'OMNI_CANN_FA_MAX_UBATCH': str(ubatch)}
        r = run_textonly_test(label, 450, extra_env=extra)
        results[ubatch] = r
        shapes_by_kv = defaultdict(list)
        for q, kv in r.get('unique_shapes_ordered', []):
            shapes_by_kv[kv].append(q)
        print(f'  ubatch={ubatch:4d}: shapes={dict(shapes_by_kv)}, NaN={r["has_nan"]}, '
              f'first_nan={r["first_nan_shape"]}, resp={r["response_preview"][:60]!r}')

    return results


def cross_section():
    """Step 1C: Cross-section sweep."""
    print("\n" + "="*70)
    print("STEP 1C: Cross-section (n_ubatch × n_x sweep)")
    print("="*70)

    results = {}
    for ubatch in [512, 384, 320, 256]:
        for n_x in [350, 400, 450, 500, 550]:
            label = f'cross_u{ubatch}_nx{n_x}'
            extra = {'OMNI_CANN_FA_MAX_UBATCH': str(ubatch)}
            r = run_textonly_test(label, n_x, extra_env=extra)
            results[(ubatch, n_x)] = r
            print(f'  ub={ubatch} nx={n_x}: NaN={r["has_nan"]}, '
                  f'first_nan={r["first_nan_shape"]}, resp={r["response_preview"][:60]!r}')

    return results


def golden_verify():
    """Step 1D: Golden bypass verification."""
    print("\n" + "="*70)
    print("STEP 1D: Golden bypass verification")
    print("="*70)

    r_text = run_textonly_test('golden_bypass', 450,
                                extra_env={'OMNI_CANN_FA_BYPASS': '1'})
    print(f'  BYPASS: NaN={r_text["has_nan"]}, resp={r_text["response_preview"][:60]!r}')

    r_text_fused = run_textonly_test('golden_fused', 450)
    print(f'  FUSED:  NaN={r_text_fused["has_nan"]}, resp={r_text_fused["response_preview"][:60]!r}')

    return {'bypass': r_text, 'fused': r_text_fused}


def main():
    print(f"PHASE 1 — FA SHAPE CHARACTERIZATION")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Logs: {LOG_DIR}")
    print(f"Results: {RESULTS_FILE}")

    all_results = {}

    # Step 1A: Verify threshold
    all_results['verify'] = verify_threshold()

    # Step 1B: n_ubatch sweep
    all_results['ubatch_sweep'] = n_ubatch_sweep()

    # Step 1C: Cross-section
    all_results['cross'] = cross_section()

    # Step 1D: Golden bypass
    all_results['golden'] = golden_verify()

    # Summary
    print("\n" + "="*70)
    print("PHASE 1 SUMMARY")
    print("="*70)

    # Aggregate shape map
    shape_map = defaultdict(lambda: {'clean': 0, 'nan': 0})
    for key, result in all_results.items():
        results_dict = result if isinstance(result, dict) else {}
        for subresult in results_dict.values():
            if not isinstance(subresult, dict) or 'unique_shapes_ordered' not in subresult:
                continue
            nan_set = set(tuple(s) for s in subresult.get('nan_shapes', []))
            for q, kv in subresult.get('unique_shapes_ordered', []):
                if (q, kv) in nan_set:
                    shape_map[(q, kv)]['nan'] += 1
                else:
                    shape_map[(q, kv)]['clean'] += 1

    print("\nSAFE SHAPES:")
    for (q, kv), counts in sorted(shape_map.items(), key=lambda x: (x[0][1], x[0][0])):
        if counts['nan'] == 0 and counts['clean'] > 0:
            print(f'  Q={q:4d} KV={kv:4d}: CLEAN ({counts["clean"]}x)')

    print("\nFAILING SHAPES:")
    for (q, kv), counts in sorted(shape_map.items(), key=lambda x: (x[0][1], x[0][0])):
        if counts['nan'] > 0:
            print(f'  Q={q:4d} KV={kv:4d}: NaN ({counts["nan"]}/{counts["clean"]+counts["nan"]}x)')

    print(f"\nFinished: {datetime.now().isoformat()}")
    return all_results

if __name__ == '__main__':
    main()
