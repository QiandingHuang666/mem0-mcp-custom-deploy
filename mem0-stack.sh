#!/bin/bash
set -euo pipefail

# mem0-stack.sh — Wrapper script for Mem0 service stack (Ollama + Qdrant + MCP Server)

PROJECT_DIR="/home/hqd/app/mem0-project"
QDRANT_PATH="${QDRANT_PATH:-$PROJECT_DIR/storage}"
OLLAMA_BIN="${OLLAMA_BIN:-/usr/local/bin/ollama}"
QDRANT_BIN="${QDRANT_BIN:-/usr/local/bin/qdrant}"

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

WAIT_TIMEOUT=60
POLL_INTERVAL=2

# PIDs of child processes
declare -A PIDS=()

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] mem0-stack: $*"
}

err() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] mem0-stack ERROR: $*" >&2
}

# Load environment file if it exists
if [ -f /etc/mem0-stack.env ]; then
    log "Loading environment from /etc/mem0-stack.env"
    set -a
    # shellcheck source=/dev/null
    source /etc/mem0-stack.env
    set +a
fi

cleanup() {
    log "Caught signal, shutting down all child processes..."
    for name in "${!PIDS[@]}"; do
        pid="${PIDS[$name]}"
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping $name (PID $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
    done

    # Wait up to 10 seconds for graceful shutdown
    for _ in $(seq 1 10); do
        all_stopped=true
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                all_stopped=false
                break
            fi
        done
        if $all_stopped; then
            break
        fi
        sleep 1
    done

    # Force kill anything still running
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log "Force killing PID $pid..."
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    wait 2>/dev/null || true
    log "All processes stopped."
}

trap cleanup SIGTERM SIGINT

wait_for() {
    local name="$1"
    local url="$2"
    local elapsed=0

    log "Waiting for $name to be ready at $url ..."
    while [ $elapsed -lt $WAIT_TIMEOUT ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            log "$name is ready."
            return 0
        fi
        sleep $POLL_INTERVAL
        elapsed=$((elapsed + POLL_INTERVAL))
    done

    err "$name did not become ready within ${WAIT_TIMEOUT}s"
    return 1
}

is_ready() {
    local url="$1"
    curl -sf "$url" >/dev/null 2>&1
}

monitor_children() {
    # If any child exits, kill them all
    for name in "${!PIDS[@]}"; do
        pid="${PIDS[$name]}"
        if ! kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null
            exit_code=$?
            err "$name (PID $pid) exited with code $exit_code"
            cleanup
            exit "$exit_code"
        fi
    done
}

# --- Start Ollama ---
if is_ready "$OLLAMA_URL/api/tags"; then
    log "Ollama is already running at $OLLAMA_URL"
else
    log "Starting Ollama..."
    "$OLLAMA_BIN" serve &
    PIDS[ollama]=$!
    log "Ollama started (PID ${PIDS[ollama]})"
    wait_for "Ollama" "$OLLAMA_URL/api/tags"
fi

# --- Start Qdrant ---
if is_ready "$QDRANT_URL/"; then
    log "Qdrant is already running at $QDRANT_URL"
else
    log "Starting Qdrant..."
    "$QDRANT_BIN" --storage-path "$QDRANT_PATH" &
    PIDS[qdrant]=$!
    log "Qdrant started (PID ${PIDS[qdrant]})"
    wait_for "Qdrant" "$QDRANT_URL/"
fi

# --- Start MCP Server ---
log "Starting MCP Server..."
cd "$PROJECT_DIR"
uv run python -m mem0_mcp_server.http_entry &
PIDS[mcp]=$!
log "MCP Server started (PID ${PIDS[mcp]})"

# --- Monitor loop ---
log "All services started. Monitoring..."
while true; do
    monitor_children
    sleep 5
done
