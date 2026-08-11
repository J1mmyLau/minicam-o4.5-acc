#!/usr/bin/env python3
"""Quick verification: does the safe dispatch fix resolve the golden failing cases?"""
import subprocess, json, os, time, select

CLI = '/workspace/llama.cpp-omni-bench-huawei/build/bin/llama-omni-eval-daily-cli'
MODEL = '/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf'

def test(label, prompt, env_extra=None, timeout=180):
    cmd = [CLI, '-m', MODEL, '-c', '40960', '-ngl', '999',
           '--n-predict', '32', '--temp', '0.0', '--top-p', '0.8', '--top-k', '100',
           '--repeat-penalty', '1.02', '--seed', '42']
    env = os.environ.copy()
    env['ASCEND_RT_VISIBLE_DEVICES'] = '0'
    if env_extra:
        env.update(env_extra)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env)
    pid = proc.pid
    start = time.time()
    ready = False
    while time.time() - start < 120:
        r, _, _ = select.select([proc.stdout], [], [], 2.0)
        if r:
            line = proc.stdout.readline()
            if not line: break
            try:
                if json.loads(line).get('type') == 'ready':
                    ready = True
                    break
            except: pass

    if not ready:
        proc.kill()
        return {'label': label, 'error': 'timeout waiting for ready', 'pid': pid}

    req = json.dumps({'type': 'infer', 'id': label, 'frames': [], 'audios': [],
                      'prompt': prompt, 'n_predict': 32}, ensure_ascii=False) + '\n'
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

    # Check for CPU fallback in stderr
    has_cpu_fallback = 'FLASH_ATTN_EXT' in stderr and 'CPU' in stderr
    nan_count = stderr.count('cann_fa_output') - stderr.count('nan=0')

    # Check if response is valid (not all underscores)
    all_us = all(c == '_' for c in resp) if resp else False
    return {
        'label': label, 'pid': pid, 'response': resp[:120],
        'all_underscores': all_us, 'nan_stderr_count': max(0, nan_count),
        'wall_s': round(time.time() - start, 1)
    }

# Test 1: Text-only n_x=450 (should now be clean with safe dispatch)
print("=== Test 1: Text-only n_x=450 (was NaN, should be clean) ===")
prompt450 = "X " * 450 + "\n\nSay hello.\n"
r = test('text450', prompt450)
print(f"  response={r['response'][:80]!r}, all_=_={r['all_underscores']}, nan={r['nan_stderr_count']}, wall={r['wall_s']}s")

# Test 2: Text-only n_x=400 (was already clean, should stay clean)
print("\n=== Test 2: Text-only n_x=400 (should stay clean) ===")
prompt400 = "X " * 400 + "\n\nSay hello.\n"
r = test('text400', prompt400)
print(f"  response={r['response'][:80]!r}, all_=_={r['all_underscores']}, nan={r['nan_stderr_count']}, wall={r['wall_s']}s")

# Test 3: OMNI_CANN_FA_SAFE_DISPATCH=0 (force-disable, should be NaN)
print("\n=== Test 3: Safe dispatch OFF (should be NaN) ===")
r = test('text450_nosafe', prompt450, {'OMNI_CANN_FA_SAFE_DISPATCH': '0'})
print(f"  response={r['response'][:80]!r}, all_=_={r['all_underscores']}, nan={r['nan_stderr_count']}, wall={r['wall_s']}s")

print("\n=== VERDICT ===")
print("Test 1 should be CLEAN (not all underscores)")
print("Test 2 should be CLEAN (not all underscores)")
print("Test 3 should be NaN (all underscores) — proves safe dispatch is working")
