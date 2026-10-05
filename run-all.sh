#!/usr/bin/env bash
# Start both Team Science development services from any checkout location.
# Supported shells: Git Bash, WSL, macOS, and Linux.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
FRONTEND_DIR="$REPO_ROOT/frontend"
STATE_DIR="$REPO_ROOT/.run"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
FRONTEND_PID_FILE="$STATE_DIR/frontend.pid"
BACKEND_PID=""
FRONTEND_PID=""
SHUTTING_DOWN=0

status() { printf '\033[0;36m-> %s\033[0m\n' "$1"; }
success() { printf '\033[0;32mOK %s\033[0m\n' "$1"; }
error() { printf '\033[0;31mERROR %s\033[0m\n' "$1" >&2; }

is_windows_shell() {
    [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OSTYPE:-}" == win32* ]]
}

pid_is_running() { kill -0 "$1" 2>/dev/null; }

stop_tree() {
    local pid="${1:-}"
    [[ -n "$pid" ]] || return 0
    pid_is_running "$pid" || return 0

    if is_windows_shell && command -v taskkill.exe >/dev/null 2>&1; then
        taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
        return 0
    fi

    local child
    if command -v pgrep >/dev/null 2>&1; then
        while read -r child; do
            [[ -n "$child" ]] && stop_tree "$child"
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    fi
    kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
    local exit_code=$?
    [[ "$SHUTTING_DOWN" -eq 0 ]] || return
    SHUTTING_DOWN=1
    trap - EXIT INT TERM HUP
    printf '\n'
    status "Stopping Team Science services..."
    stop_tree "$FRONTEND_PID"
    stop_tree "$BACKEND_PID"

    local deadline=$((SECONDS + 8))
    while (( SECONDS < deadline )); do
        if { [[ -z "$FRONTEND_PID" ]] || ! pid_is_running "$FRONTEND_PID"; } &&
           { [[ -z "$BACKEND_PID" ]] || ! pid_is_running "$BACKEND_PID"; }; then
            break
        fi
        sleep 0.25
    done

    [[ -z "$FRONTEND_PID" ]] || kill -KILL "$FRONTEND_PID" 2>/dev/null || true
    [[ -z "$BACKEND_PID" ]] || kill -KILL "$BACKEND_PID" 2>/dev/null || true
    rm -f -- "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
    success "Services stopped"
    exit "$exit_code"
}

trap cleanup EXIT INT TERM HUP
mkdir -p -- "$STATE_DIR"

if [[ -f "$BACKEND_PID_FILE" || -f "$FRONTEND_PID_FILE" ]]; then
    status "Cleaning up services left by an earlier run..."
    bash "$REPO_ROOT/stop-all.sh" --tracked-only
fi

if is_windows_shell; then
    VENV_PYTHON="$REPO_ROOT/.venv/Scripts/python.exe"
else
    VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
fi

find_bootstrap_python() {
    if command -v python3 >/dev/null 2>&1; then
        printf '%s\n' "python3"
    elif command -v python >/dev/null 2>&1; then
        printf '%s\n' "python"
    elif command -v py >/dev/null 2>&1; then
        printf '%s\n' "py"
    else
        return 1
    fi
}

status "Checking development tools..."
BOOTSTRAP_PYTHON="$(find_bootstrap_python)" || {
    error "Python was not found. Install Python 3.11+ and try again."
    exit 1
}
command -v node >/dev/null 2>&1 || { error "Node.js was not found."; exit 1; }
command -v npm >/dev/null 2>&1 || { error "npm was not found."; exit 1; }

read -r NODE_MAJOR NODE_MINOR NODE_PATCH < <(
    node -p 'process.versions.node.split(".").map(Number).join(" ")'
)
(( NODE_MAJOR > 22 || (NODE_MAJOR == 22 && NODE_MINOR >= 22) )) || {
    error "Node.js 22.22.0 or newer is required; found $(node --version)."
    exit 1
}

if [[ -e "$VENV_PYTHON" ]] && ! "$VENV_PYTHON" --version >/dev/null 2>&1; then
    status "Repairing a stale Python virtual environment..."
    "$BOOTSTRAP_PYTHON" -m venv --clear "$REPO_ROOT/.venv"
elif [[ ! -x "$VENV_PYTHON" ]]; then
    status "Creating the repository-local Python environment..."
    "$BOOTSTRAP_PYTHON" -m venv "$REPO_ROOT/.venv"
fi

if ! "$VENV_PYTHON" -c 'import fastapi, pandas, sqlalchemy, uvicorn' >/dev/null 2>&1; then
    status "Installing backend dependencies..."
    "$VENV_PYTHON" -m pip install -r "$REPO_ROOT/backend/requirements.txt"
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    status "Installing frontend dependencies from package-lock.json..."
    (cd "$FRONTEND_DIR" && npm ci)
fi

if [[ ! -f "$FRONTEND_DIR/.env" && -f "$FRONTEND_DIR/.env.example" ]]; then
    cp -- "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env"
fi

wait_for_url() {
    local name="$1" url="$2" pid="$3"
    local attempt
    for ((attempt = 1; attempt <= 60; attempt++)); do
        pid_is_running "$pid" || { error "$name exited before it became ready."; return 1; }
        if command -v curl >/dev/null 2>&1 && curl --silent --fail --max-time 1 "$url" >/dev/null 2>&1; then
            success "$name is ready"
            return 0
        fi
        sleep 1
    done
    error "$name did not become ready at $url within 60 seconds."
    return 1
}

write_pid_file() {
    local file="$1" pid="$2" identity
    identity="$(ps -p "$pid" -f 2>/dev/null | tail -n 1 | sed 's/^[[:space:]]*//' || true)"
    printf '%s\n%s\n' "$pid" "$identity" > "$file"
}

status "Starting backend with reload limited to backend Python files..."
(
    cd "$REPO_ROOT"
    exec "$VENV_PYTHON" -m uvicorn backend.api.main:app \
        --reload --reload-dir "$REPO_ROOT/backend" \
        --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!
write_pid_file "$BACKEND_PID_FILE" "$BACKEND_PID"
wait_for_url "Backend" "http://127.0.0.1:8000/health" "$BACKEND_PID"

status "Starting frontend development server..."
(
    cd "$FRONTEND_DIR"
    exec npm run dev
) &
FRONTEND_PID=$!
write_pid_file "$FRONTEND_PID_FILE" "$FRONTEND_PID"
wait_for_url "Frontend" "http://127.0.0.1:5173/" "$FRONTEND_PID"

printf '\n'
success "Team Science is running"
printf '  Frontend: http://127.0.0.1:5173\n'
printf '  Backend:  http://127.0.0.1:8000\n'
printf '  API docs: http://127.0.0.1:8000/docs\n'
printf '  Stop all: bash ./stop-all.sh\n'
printf '  Ctrl+C also stops both services.\n\n'

while pid_is_running "$BACKEND_PID" && pid_is_running "$FRONTEND_PID"; do
    sleep 1
done

error "A development service stopped unexpectedly. Shutting down the other service."
exit 1
