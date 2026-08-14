#!/usr/bin/env bash
# run_selftest.sh — 官方 Gate 工具链离线自检（不起服务、不占 NPU、不发请求）
# 用法：bash submission/tests/run_selftest.sh
#   可选 SELFTEST_MODEL_PATH=<真实模型> 启用 run_performance candidate exit-0 dry-run 检查。
# 完整命令/结果记录见 docs/competition-submission/OFFICIAL_GATE_TOOLING_SELFTEST.md
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

PASS=0; FAIL=0
say()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
expect_rc() { # expect_rc <expected> <desc> <cmd...>
  local exp="$1" desc="$2"; shift 2
  if "$@" >/dev/null 2>&1; then rc=0; else rc=$?; fi
  if [ "${rc}" = "${exp}" ]; then ok "${desc} (rc=${rc})"; else bad "${desc} (rc=${rc}, exp=${exp})"; fi
}

say "== 1. python --help（三脚本可执行） =="
expect_rc 0 "analyze_chunk_rtf.py --help" python3 submission/scripts/analyze_chunk_rtf.py --help
expect_rc 0 "run_chunk_rtf_client.py --help" python3 submission/scripts/run_chunk_rtf_client.py --help
expect_rc 0 "check_baseline_candidate_symmetry.py --help" python3 submission/scripts/check_baseline_candidate_symmetry.py --help

say "== 2. Gate 脚本 --dry-run（缺官方 Harness → rc=2，不起服务不发请求） =="
expect_rc 2 "run_daily_omni.sh --dry-run" bash submission/scripts/run_daily_omni.sh --dry-run
expect_rc 2 "run_tts_seed.sh --dry-run" bash submission/scripts/run_tts_seed.sh --dry-run
expect_rc 2 "run_video_mme.sh --dry-run" bash submission/scripts/run_video_mme.sh --dry-run

say "== 3. run_performance.sh --dry-run 配置/资产校验 =="
expect_rc 3 "无效 MODE → 3" env MODE=bogus bash submission/scripts/run_performance.sh --dry-run
expect_rc 3 "baseline 未给 BASELINE_SERVER_BIN → 3" env MODE=baseline bash submission/scripts/run_performance.sh --dry-run
expect_rc 2 "baseline 二进制不存在 → 2" env MODE=baseline BASELINE_SERVER_BIN=/nonexistent bash submission/scripts/run_performance.sh --dry-run
if [ -n "${SELFTEST_MODEL_PATH:-}" ] && [ -f "${SELFTEST_MODEL_PATH}" ]; then
  expect_rc 0 "candidate --dry-run 资产齐全 → 0" env MODEL_PATH="${SELFTEST_MODEL_PATH}" bash submission/scripts/run_performance.sh candidate --dry-run
else
  say "  [SKIP] candidate exit-0 dry-run（需 SELFTEST_MODEL_PATH 指向真实模型）"
fi

say "== 4. valid_audio 单测（10 排除原因 + WAV fixture + --warmup CLI） =="
if python3 -m unittest submission/tests/test_analyze_chunk_rtf.py >/dev/null 2>&1; then
  ok "test_analyze_chunk_rtf.py 全部用例"
else
  bad "test_analyze_chunk_rtf.py 有失败（见下）"
  python3 -m unittest submission/tests/test_analyze_chunk_rtf.py 2>&1 | tail -40 || true
fi

say "== 5. 对称性 fixture（matching=0 / mismatched=1 / missing=2） =="
if python3 submission/tests/make_symmetry_fixture.py >/dev/null 2>&1; then
  ok "symmetry fixtures 全部符合预期退出码"
else
  bad "symmetry fixtures 失败（见下）"
  python3 submission/tests/make_symmetry_fixture.py 2>&1 | tail -20 || true
fi

say "== 6. 私有路径扫描（submission/ 禁止 /workspace /home /tmp 代码行字面量） =="
if python3 submission/tests/check_no_private_paths.py >/dev/null 2>&1; then
  ok "submission/ 无私有绝对路径"
else
  bad "submission/ 存在私有路径（见下）"
  python3 submission/tests/check_no_private_paths.py 2>&1 | tail -30 || true
fi

say "== 7. 输出目录不在 /tmp（默认 OUTPUT_ROOT 派生自 REPO_ROOT） =="
if ! grep -q 'OUTPUT_ROOT.*/tmp' submission/config/server.env 2>/dev/null \
   && ! grep -n '^[^#]*/tmp' submission/scripts/run_performance.sh submission/scripts/start_server.sh 2>/dev/null | grep -v 'set_env.sh' ; then
  ok "默认输出目录均派生自 REPO_ROOT（无 /tmp 依赖）"
else
  bad "发现 /tmp 输出依赖"
fi

# 清理测试临时产物
rm -rf submission/tests/_out

say ""
printf 'SELFTEST_RESULT PASS=%d FAIL=%d\n' "${PASS}" "${FAIL}"
[ "${FAIL}" = "0" ]
