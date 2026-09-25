#!/usr/bin/env bash
# ==============================================================================
# Indian Financial Document Classification Engine - Single Unified Runner
# Starts FastAPI Backend, ARQ Worker, and Vite Frontend concurrently.
# Remains open while running; cleanly terminates all services on exit.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================================="
echo " Starting DocClassifier Engine (Backend + ARQ Worker + Frontend)"
echo "=================================================================="

# 1. Activate Python Virtual Environment
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[+] Activating virtual environment from venv/bin/activate..."
    source "$SCRIPT_DIR/venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/Scripts/activate" ]; then
    echo "[+] Activating virtual environment from venv/Scripts/activate..."
    source "$SCRIPT_DIR/venv/Scripts/activate"
elif [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    echo "[+] Activating virtual environment from .venv/bin/activate..."
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "[!] No virtual environment found in ./venv or ./.venv. Using system Python."
fi

PYTHON_CMD=$(which python3 || which python)

# 2. Check Node.js and npm
if ! command -v npm &> /dev/null; then
    echo "[ERROR] 'npm' was not found in PATH. Please install Node.js and npm to run the frontend."
    exit 1
fi

# Ensure frontend dependencies are installed
if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    echo "[+] Installing frontend dependencies (npm install)..."
    (cd "$SCRIPT_DIR/frontend" && npm install)
fi

# 3. Clean up on exit handler
PIDS=()
cleanup() {
    echo ""
    echo "[*] Terminating DocClassifier services..."
    for pid in "${PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            pkill -P "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
        fi
    done

    # Free listening ports if processes remain
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 5173/tcp 2>/dev/null || true

    echo "[✓] All services stopped cleanly. Closing..."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 4. Start ARQ Distributed Worker (PaddleOCR + Classification)
echo "[1/3] Starting ARQ Worker Process..."
$PYTHON_CMD -m arq app.worker.WorkerSettings &
PIDS+=($!)

# 5. Start FastAPI Backend Server
echo "[2/3] Starting FastAPI Server on http://localhost:8000..."
$PYTHON_CMD -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
PIDS+=($!)

# 6. Start Vite Frontend Dashboard
echo "[3/3] Starting Vite Frontend on http://localhost:5173..."
(cd "$SCRIPT_DIR/frontend" && npm run dev) &
PIDS+=($!)

echo ""
echo "=================================================================="
echo " DocClassifier Services Running Successfully!"
echo " - Enterprise UI:     http://localhost:5173"
echo " - FastAPI API Root:  http://localhost:8000"
echo " - Swagger OpenAPI:   http://localhost:8000/docs"
echo " - Health Check:      http://localhost:8000/health"
echo ""
echo " Press [Ctrl+C] to stop all services and close."
echo "=================================================================="

# Block and wait for background processes
wait
