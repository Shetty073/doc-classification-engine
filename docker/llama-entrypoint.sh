#!/bin/sh
set -e

# Default configurations
MODEL_PATH="${MODEL_PATH:-/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf}"
CTX_SIZE="${CTX_SIZE:-4096}"
N_GPU_LAYERS="${N_GPU_LAYERS:-0}"
THREADS="${THREADS:-4}"
BATCH_SIZE="${BATCH_SIZE:-512}"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
TEMPERATURE="${TEMPERATURE:-0.05}"

echo "=========================================================="
echo " Starting llama.cpp Server Container"
echo "=========================================================="
echo " Model Path:      $MODEL_PATH"
echo " Context Size:    $CTX_SIZE"
echo " GPU Offload (-ngl): $N_GPU_LAYERS"
echo " CPU Threads:     $THREADS"
echo " Batch Size:      $BATCH_SIZE"
echo " Host / Port:     $HOST:$PORT"
echo " Temperature:     $TEMPERATURE"
echo "=========================================================="

if [ ! -f "$MODEL_PATH" ]; then
    echo "WARNING: Model file not found at '$MODEL_PATH'!"
    echo "Please ensure your GGUF model is mounted into the container (e.g. -v ./models:/models)."
    echo "Available files in /models:"
    ls -lah /models || true
fi

# Locate llama-server binary
SERVER_BIN="/llama-server"
if [ ! -f "$SERVER_BIN" ]; then
    if command -v llama-server >/dev/null 2>&1; then
        SERVER_BIN="llama-server"
    else
        SERVER_BIN="/app/llama-server"
    fi
fi

exec $SERVER_BIN \
    -m "$MODEL_PATH" \
    -c "$CTX_SIZE" \
    -ngl "$N_GPU_LAYERS" \
    -t "$THREADS" \
    -b "$BATCH_SIZE" \
    --temp "$TEMPERATURE" \
    --host "$HOST" \
    --port "$PORT" \
    $EXTRA_ARGS "$@"
