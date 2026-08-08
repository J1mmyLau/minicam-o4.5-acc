#!/usr/bin/env bash
set -euo pipefail
source /usr/local/Ascend/cann/set_env.sh
export OMNI_T2W_DEVICE="${OMNI_T2W_DEVICE:-cann-flow-only}"
echo "CANN 9.1: ${ASCEND_HOME_PATH}"
echo "OPS: ${ASCEND_OPP_PATH}"
echo "T2W: ${OMNI_T2W_DEVICE}"
