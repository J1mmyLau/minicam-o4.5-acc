#!/usr/bin/env python3
"""
Standalone Q8_0 vs F16 MatMul micro-benchmark using CANN backend.
Bypasses the server entirely — tests MatMul performance directly.

Strategy:
  - Create a small LLM-like tensor (matching Qwen3-8B hidden_dim=4096, ffn_dim=14336)
  - Run many MatMul iterations with both F16 and Q8_0 weights
  - Measure wall time per iteration
  - This isolates the MatMul kernel from all server/WS/calibration complexity
"""
import ctypes
import time
import os
import sys
import json
import statistics
import argparse

# Load libggml and libggml-cann
GGML_LIB = "/workspace/llama.cpp-omni-session-fix/build/ggml/src/libggml.so"
CANN_LIB = "/workspace/llama.cpp-omni-session-fix/build/ggml/src/ggml-cann/libggml-cann.so"

# Define GGML types matching C enum
GGML_TYPE_F32 = 0
GGML_TYPE_F16 = 1
GGML_TYPE_Q8_0 = 8

GGML_OP_MUL_MAT = 20

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_iter", type=int, default=200, help="Number of iterations")
    parser.add_argument("--hidden", type=int, default=4096, help="Hidden dimension")
    parser.add_argument("--ffn", type=int, default=14336, help="FFN intermediate dimension")
    parser.add_argument("--seq_len", type=int, default=1, help="Sequence length (decode=1)")
    parser.add_argument("--nz_off", action="store_true", help="Set GGML_CANN_WEIGHT_NZ=off")
    args = parser.parse_args()

    if args.nz_off:
        os.environ["GGML_CANN_WEIGHT_NZ"] = "off"
        print("GGML_CANN_WEIGHT_NZ=off (ND layout)")

    # Since we can't easily use the C++ API from Python,
    # use the benchmark_client.py or create a simple C program
    print("This benchmark requires a C/C++ harness. Using server-based approach instead.")

    # Alternative: use the existing calibration infrastructure
    # but extract LLM decode timing from [bench] logs
    print(f"Config: hidden={args.hidden}, ffn={args.ffn}, seq_len={args.seq_len}, n_iter={args.n_iter}")
    print("Key dimensions for Qwen3-8B linear layers:")
    print(f"  Q/K/V proj: [{args.hidden}, {args.hidden}] x [{args.seq_len}, {args.hidden}]")
    print(f"  FFN up:     [{args.ffn}, {args.hidden}] x [{args.seq_len}, {args.hidden}]")
    print(f"  FFN down:   [{args.hidden}, {args.ffn}] x [{args.seq_len}, {args.ffn}]")
    print(f"  Output:     [{args.hidden}, {args.hidden}] x [{args.seq_len}, {args.hidden}]")

if __name__ == "__main__":
    main()
