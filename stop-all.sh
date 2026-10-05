#!/usr/bin/env bash
# Stop Team Science development services started from this checkout.

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.run"
TRACKED_ONLY=0
[[ "${1:-}" == "--tracked-only" ]] && TRACKED_ONLY=1

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

stop_pid_file() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    local pid expected_identity current_identity
    IFS= read -r pid < "$file"
    pid="${pid//[^0-9]/}"
    expected_identity="$(tail -n +2 "$file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && pid_is_running "$pid"; then
        current_identity="$(ps -p "$pid" -f 2>/dev/null | tail -n 1 | sed 's/^[[:space:]]*//' || true)"
        if [[ -n "$expected_identity" && "$current_identity" == "$expected_identity" ]]; then
            printf 'Stopping verified process tree %s...\n' "$pid"
            stop_tree "$pid"
        else
            printf 'Skipping stale PID %s because its process identity no longer matches.\n' "$pid" >&2
        fi
    fi
    rm -f -- "$file"
}

stop_pid_file "$STATE_DIR/frontend.pid"
stop_pid_file "$STATE_DIR/backend.pid"

if [[ "$TRACKED_ONLY" -eq 0 ]]; then
    if is_windows_shell && command -v netstat.exe >/dev/null 2>&1; then
        for port in 5173 8000; do
            while read -r pid; do
                [[ -n "$pid" && "$pid" != "0" ]] || continue
                printf 'Stopping process %s listening on port %s...\n' "$pid" "$port"
                taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
            done < <(netstat.exe -ano -p tcp 2>/dev/null | awk -v port=":$port" '$2 ~ port && $4 == "LISTENING" {print $5}' | sort -u)
        done
    elif command -v lsof >/dev/null 2>&1; then
        for port in 5173 8000; do
            while read -r pid; do
                [[ -n "$pid" ]] && stop_tree "$pid"
            done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        done
    elif command -v fuser >/dev/null 2>&1; then
        fuser -k 5173/tcp 8000/tcp 2>/dev/null || true
    fi
fi

printf 'Team Science development services are stopped.\n'
