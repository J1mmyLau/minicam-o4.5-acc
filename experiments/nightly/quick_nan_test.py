#!/usr/bin/env python3
"""Test: does FA produce NaN at high KV with small Q?"""
import subprocess, json, os, time, select

CLI = '/workspace/llama.cpp-omni-bench-huawei/build/bin/llama-omni-eval-daily-cli'
MODEL = '/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf'

def test(label, prompt, n_predict=32, extra_env=None, timeout=300):
    cmd = [CLI, '-m', MODEL, '-c', '40960', '-ngl', '999',
           '--n-predict', str(n_predict), '--temp', '0.0', '--top-p', '0.8',
           '--top-k', '100', '--repeat-penalty', '1.02', '--seed', '42']
    env = os.environ.copy()
    env['ASCEND_RT_VISIBLE_DEVICES'] = '0'
    env['OMNI_CANN_FA_MAX_UBATCH'] = '384'
    env['OMNI_CANN_FA_NAN_CHECK'] = '1'  # ENABLE NaN check
    if extra_env:
        env.update(extra_env)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env)
    start = time.time()
    # Wait for ready
    while time.time() - start < 120:
        r, _, _ = select.select([proc.stdout], [], [], 2.0)
        if r:
            line = proc.stdout.readline()
            if not line: break
            try:
                if json.loads(line).get('type') == 'ready':
                    break
            except: pass

    req = json.dumps({'type': 'infer', 'id': label, 'frames': [], 'audios': [],
                      'prompt': prompt, 'n_predict': n_predict}, ensure_ascii=False) + '\n'
    proc.stdin.write(req.encode())
    proc.stdin.flush()

    result_line = ''
    while time.time() - start < timeout:
        r, _, _ = select.select([proc.stdout], [], [], 5.0)
        if r:
            line = proc.stdout.readline()
            if line:
                result_line = line.decode('utf-8', errors='replace')
                break
        if proc.poll() is not None:
            break

    proc.stdin.close()
    try: proc.wait(timeout=30)
    except: proc.kill()

    stderr = proc.stderr.read().decode('utf-8', errors='replace')
    resp = ''
    if result_line:
        try: resp = json.loads(result_line).get('response', '')
        except: pass

    # Extract NaN info
    nan_lines = [l for l in stderr.split('\n') if 'cann_fa_output' in l and 'nan=' in l]
    nan_counts = []
    for l in nan_lines:
        import re
        m = re.search(r'nan=(\d+)', l)
        if m: nan_counts.append(int(m.group(1)))

    all_us = all(c == '_' for c in resp) if resp else False
    return {
        'label': label,
        'all_underscores': all_us,
        'resp_len': len(resp),
        'resp_preview': resp[:100],
        'wall_s': round(time.time() - start, 1),
        'nan_checks': len(nan_lines),
        'nan_nonzero': sum(1 for n in nan_counts if n > 0),
        'nan_max': max(nan_counts) if nan_counts else 0,
    }

# Test 1: Very long text prompt to build up large KV (~20000 tokens)
print("=== Test 1: Long text prompt (KV ~ 20000) ===")
long_prompt = ("The quick brown fox jumps over the lazy dog. " * 500 +  # ~5000 tokens
               "\n\nNow I will describe the history of computing. " +
               "Computers have evolved dramatically over the past century. " * 300 +  # ~3000 tokens  
               "\n\n" +
               "Python is a high-level programming language. " * 300 +  # ~3000 tokens
               "\n\n" +
               "Machine learning is a subset of artificial intelligence. " * 300 +  # ~5000 tokens
               "\n\n" +
               "The transformer architecture was introduced in 2017. " * 200 +  # ~4000 tokens
               "\n\nPlease summarize the above text in one sentence.")
r = test('long_text', long_prompt, n_predict=32, timeout=600)
print(f"  underscores={r['all_underscores']}, resp='{r['resp_preview']}', wall={r['wall_s']}s")
print(f"  nan_checks={r['nan_checks']}, nan_nonzero={r['nan_nonzero']}, nan_max={r['nan_max']}")

# Test 2: Medium text prompt (KV ~ 5000) — should be clean
print("\n=== Test 2: Medium text prompt (KV ~ 5000) ===")
med_prompt = ("The quick brown fox jumps over the lazy dog. " * 200 +
              "\n\nSay hello in Chinese.")
r = test('med_text', med_prompt, n_predict=16, timeout=300)
print(f"  underscores={r['all_underscores']}, resp='{r['resp_preview']}', wall={r['wall_s']}s")
print(f"  nan_checks={r['nan_checks']}, nan_nonzero={r['nan_nonzero']}, nan_max={r['nan_max']}")

# Test 3: Short control (should be clean)
print("\n=== Test 3: Short control ===")
r = test('short', "Say hello in Chinese.\n", n_predict=16)
print(f"  underscores={r['all_underscores']}, resp='{r['resp_preview']}', wall={r['wall_s']}s")
print(f"  nan_checks={r['nan_checks']}, nan_nonzero={r['nan_nonzero']}, nan_max={r['nan_max']}")

print("\n=== FINDINGS ===")
