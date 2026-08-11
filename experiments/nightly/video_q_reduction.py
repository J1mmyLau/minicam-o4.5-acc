#!/usr/bin/env python3
"""Find safe Q threshold for video: binary search n_ubatch with FA_NAN_CHECK=1.

Key finding: video Q=32@KV=768 produces NaN (content-dependent),
while text Q=32@KV=768 is CLEAN. Video NaN threshold is LOWER than text.
This script finds the maximum safe n_ubatch for video.
"""
import subprocess, json, os, sys, time, shutil
from pathlib import Path

EVAL_DIR = Path('/workspace/llama.cpp-omni-bench-huawei/evaluation')
CONFIG_ENV = EVAL_DIR / 'config.env'
MODEL = '/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf'
CLI = '/workspace/llama.cpp-omni-bench-huawei/build/bin/llama-omni-eval-cli'

def load_config():
    """Parse config.env for key-value pairs."""
    cfg = {}
    with open(CONFIG_ENV) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg

def run_single_video_sample(ubatch, timeout=300):
    """Run ONE video sample (fFjv93ACGo8.mp4 question 001-1) with given n_ubatch."""
    cfg = load_config()

    # Build env
    env = os.environ.copy()
    env['ASCEND_RT_VISIBLE_DEVICES'] = '0'
    env['OMNI_CANN_FA_MAX_UBATCH'] = str(ubatch)
    env['OMNI_CANN_FA_SAFE_DISPATCH'] = '1'
    env['OMNI_CANN_FA_NAN_CHECK'] = '1'
    env['OMNI_CANN_FA_EVERY'] = '1'
    env['SAMPLER_SEED'] = '42'

    # Use the eval_cpp_pipeline.py directly for one sample
    # Construct the minimal video request
    video_path = EVAL_DIR / 'appendix/videomme/data/fFjv93ACGo8.mp4'
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}")
        return {'error': 'video_not_found'}

    # Prepare frames directory
    work_dir = Path('/tmp/video_q_reduction')
    work_dir.mkdir(parents=True, exist_ok=True)

    # Write a minimal test JSONL
    test_jsonl = work_dir / 'test_sample.jsonl'
    with open(test_jsonl, 'w') as f:
        sample = {
            'id': 'test_001',
            'video': str(video_path),
            'question': 'What color is the car in the video?',
            'choices': ['Red', 'Blue', 'White', 'Black'],
            'answer': 0,
            'fps': 0.861,  # From the smoke log
        }
        json.dump(sample, f)
        f.write('\n')

    # Run the eval pipeline
    cmd = [
        sys.executable, str(EVAL_DIR / 'eval_cpp_pipeline.py'),
        '--in-jsonl', str(test_jsonl),
        '--out-jsonl', str(work_dir / 'output.jsonl'),
        '--cli', CLI,
        '--model', MODEL,
        '--max-slice-nums', '0',
        '--n-predict', '32',  # Small for speed
        '--temp', '0.0',
        '--top-p', '0.8',
        '--top-k', '100',
        '--repeat-penalty', '1.02',
        '--seed', '42',
        '--n-gl', '999',
        '--ctx-size', '40960',
    ]

    print(f"\n{'='*60}")
    print(f"[n_ubatch={ubatch}] Running: {' '.join(cmd)}")
    print(f"[n_ubatch={ubatch}] FA_NAN_CHECK=1, FA_EVERY=1")
    print(f"{'='*60}")

    t0 = time.time()
    proc = subprocess.Popen(
        cmd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors='replace'
    )

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return {'error': 'timeout', 'ubatch': ubatch}

    elapsed = time.time() - t0

    # Parse FA_NAN_CHECK from stderr
    nan_lines = []
    fa_every_count = 0
    first_nan = None
    for line in stderr.split('\n'):
        if 'cann_fa_output' in line:
            nan_lines.append(line.strip())
            # Parse: q_seq=X kv_seq=Y checked=Z nan=N
            import re
            m = re.search(r'q_seq=(\d+)\s+kv_seq=(\d+)\s+.*nan=(\d+)', line)
            if m:
                q_seq = int(m.group(1))
                kv_seq = int(m.group(2))
                nan_count = int(m.group(3))
                if nan_count > 0 and first_nan is None:
                    first_nan = {'q_seq': q_seq, 'kv_seq': kv_seq, 'nan': nan_count}
        if 'cann_fa_EVERY' in line:
            fa_every_count += 1

    # Parse output
    response = ''
    try:
        result = json.loads(stdout.strip()) if stdout.strip() else {}
        response = result.get('response', '')[:120]
    except:
        response = stdout[:200] if stdout else ''

    all_underscores = all(c == '_' for c in response.replace(' ', '')) if response else False

    result = {
        'ubatch': ubatch,
        'elapsed_s': round(elapsed, 1),
        'response': response,
        'all_underscores': all_underscores,
        'nan_check_lines': len(nan_lines),
        'first_nan': first_nan,
        'fa_every_count': fa_every_count,
        'has_nan': any('nan=' in l and 'nan=0' not in l for l in nan_lines),
    }

    print(f"[n_ubatch={ubatch}] Result: elapsed={elapsed:.1f}s, response={response[:80]!r}")
    print(f"[n_ubatch={ubatch}] FA_NAN_CHECK: {len(nan_lines)} lines, has_nan={result['has_nan']}")
    if first_nan:
        print(f"[n_ubatch={ubatch}] FIRST NaN: Q={first_nan['q_seq']} KV={first_nan['kv_seq']} nan={first_nan['nan']}")

    return result

def main():
    # Test decreasing n_ubatch: start with the smallest that might work
    # We know 32 fails. Try 16, 8, 4, 2, 1
    ubatch_values = [16, 8, 4, 2, 1]

    results = []
    for ub in ubatch_values:
        r = run_single_video_sample(ub)
        results.append(r)

        # If clean, we found the safe threshold
        if not r.get('has_nan') and not r.get('all_underscores'):
            print(f"\n*** CLEAN at n_ubatch={ub}! Safe Q <= {ub} ***")
            # Don't break — keep going to confirm
        else:
            print(f"\n*** STILL NaN at n_ubatch={ub} ***")

    print("\n" + "="*60)
    print("REDUCTION SUMMARY")
    print("="*60)
    for r in results:
        status = "CLEAN" if (not r.get('has_nan') and not r.get('all_underscores')) else "NaN_OR_FAIL"
        print(f"  n_ubatch={r['ubatch']:>3}: {status:12s}  elapsed={r['elapsed_s']:6.1f}s  "
              f"first_nan={r.get('first_nan')}  resp={r.get('response', '')[:60]!r}")

    # Save results
    out = Path('/workspace/llama.cpp-omni-bench-huawei/experiments/nightly/video_q_reduction.json')
    import json as j
    with open(out, 'w') as f:
        j.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out}")

if __name__ == '__main__':
    main()
