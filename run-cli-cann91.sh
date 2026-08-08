#!/usr/bin/env bash
set -euo pipefail
source /usr/local/Ascend/cann/set_env.sh
export OMNI_T2W_DEVICE=cann-flow-only
exec /workspace/llama.cpp-omni-token2wav-cann/build-cann91/bin/llama-omni-cli "$@"
