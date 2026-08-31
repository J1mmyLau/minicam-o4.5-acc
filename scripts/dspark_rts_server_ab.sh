#!/bin/bash
# DSpark 双工投机开关：omni.cpp 读 OMNI_SPEC_DRAFT（-md 不被 omni_init 消费）
export OMNI_SPEC_DRAFT=/workspace/models/dspark-stage11/dspark_stage11-draft-q8mixed-C.gguf
exec /workspace/llama-cpp-upstream-dspark/build/bin/llama-omni-server "$@"
